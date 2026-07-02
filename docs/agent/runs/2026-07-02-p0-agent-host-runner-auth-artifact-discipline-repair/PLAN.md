# Plan

Task id: `P0_AGENT_HOST_RUNNER_AUTH_ARTIFACT_DISCIPLINE_REPAIR_2026_07_02`

Plan:

1. Recover the useful changes from canonical checkout
   `/var/lib/kolibri-agent/repo` after the task worktree was created empty.
2. Keep the repair branch limited to Agent Host runner, Factory Control fail
   metadata, regression tests, and this run artifact directory.
3. Preserve unrelated frontend dirty work in the canonical checkout without
   committing it into the repair branch.
4. Verify the runner contract and Factory Control routing/failure paths with
   focused remote tests on `mesh-agent-04`.
5. Push a repair branch only; do not push `main`, force push, run Mac-local
   tests, or print secrets.
