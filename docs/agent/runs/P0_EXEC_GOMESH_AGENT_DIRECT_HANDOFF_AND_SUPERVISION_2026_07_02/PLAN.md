# Plan

Task id: `P0_EXEC_GOMESH_AGENT_DIRECT_HANDOFF_AND_SUPERVISION_2026_07_02`

Goal: find the active GoMesh development agent on `primary-candidate` / Primorye, deliver owner rules directly, collect branch/status, and set a monitoring/review loop that produces useful PR artifacts.

Execution plan:

1. Use the Kolibri GoMesh gateway guardrails before touching any GoMesh routing or runtime state.
2. Verify the live Fabric API route and avoid stale listeners.
3. Locate the active GoMesh supervisor evidence from the control plane.
4. Submit an executable owner-rules monitor/review task to `primary-candidate`.
5. Poll the new task for lease/status.
6. Record artifacts, tests, blockers, and the next exact command.

Safety constraints:

- No secrets, PSKs, tokens, cookies, or env values printed.
- No destructive git commands.
- No force push and no push to `main`.
- No dirty runtime checkout modification.
- Code changes, if needed by the remote GoMesh agent, must use a clean remote worktree plus branch/PR.
